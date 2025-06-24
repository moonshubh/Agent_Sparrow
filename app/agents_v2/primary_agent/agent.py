import logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

import os
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from app.agents_v2.primary_agent.schemas import PrimaryAgentState
from typing import Iterator, List, AsyncIterator # Added for streaming return type and List
from app.agents_v2.primary_agent.tools import mailbird_kb_search, tavily_web_search
from qdrant_client import QdrantClient
from langchain_community.vectorstores.qdrant import Qdrant
from langchain_google_genai import embeddings as gen_embeddings
from opentelemetry import trace
import anyio
from opentelemetry.trace import Status, StatusCode
from app.db.embedding_utils import find_similar_documents, SearchResult as InternalSearchResult # Added for internal search

# Import Agent Sparrow modular prompt system
from app.agents_v2.primary_agent.prompts import (
    load_agent_sparrow_prompt, 
    PromptLoadConfig, 
    PromptVersion,
    EmotionTemplates,
    ResponseFormatter
)

# Import Agent Sparrow reasoning framework
from app.agents_v2.primary_agent.reasoning import (
    ReasoningEngine,
    ReasoningConfig,
    ReasoningState
)

# Import Agent Sparrow structured troubleshooting framework
from app.agents_v2.primary_agent.troubleshooting import (
    TroubleshootingEngine,
    TroubleshootingConfig,
    TroubleshootingState,
    TroubleshootingSessionManager
)

# Get a tracer instance for OpenTelemetry
tracer = trace.get_tracer(__name__)

# Load environment variables
load_dotenv()

# Ensure the GEMINI_API_KEY is set
if "GEMINI_API_KEY" not in os.environ:
    logger.error("GEMINI_API_KEY not found in environment variables.")
    raise ValueError("GEMINI_API_KEY not found in environment variables.")
else:
    logger.debug("GEMINI_API_KEY found.")

# Qdrant setup (assumes local Qdrant running or env vars set)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("KB_COLLECTION", "mailbird_kb")

# Threshold for deciding if KB docs are relevant
RELEVANCE_THRESHOLD = float(os.getenv("KB_RELEVANCE_THRESHOLD", "0.25"))
INTERNAL_SEARCH_SIMILARITY_THRESHOLD = 0.75  # Trigger web search if best internal score is below this (higher is better for similarity)
MIN_INTERNAL_RESULTS_FOR_NO_WEB_SEARCH = 2 # If we get at least this many good results, maybe skip web search

# Build embeddings & vector store interface
emb = gen_embeddings.GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=os.environ.get("GEMINI_API_KEY"))
qdrant_client = QdrantClient(url=QDRANT_URL)
vector_store = Qdrant(client=qdrant_client, collection_name=QDRANT_COLLECTION, embeddings=emb)

# 1. Initialize the model
# We use a temperature of 0 to get more deterministic results.
logger.info("Initializing ChatGoogleGenerativeAI model")
try:
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }
    model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", # Updated to latest 2.5 Flash model as per user
        temperature=0,
        google_api_key=os.environ.get("GEMINI_API_KEY"),
        safety_settings=safety_settings,
        convert_system_message_to_human=True # Recommended for some Gemini models with system messages
    )
    logger.info("ChatGoogleGenerativeAI model initialized")
except Exception as e:
    logger.exception("Error during ChatGoogleGenerativeAI initialization: %s", e)
    raise

# 2. Bind the tool to the model
logger.debug("Binding tools to model")
model_with_tools = model.bind_tools([mailbird_kb_search, tavily_web_search])
logger.info("Tools bound to model.")

# 3. Initialize Agent Sparrow Troubleshooting System
logger.info("Initializing Agent Sparrow structured troubleshooting system")
try:
    # Initialize troubleshooting configuration
    troubleshooting_config = TroubleshootingConfig(
        enable_adaptive_workflows=True,
        enable_progressive_complexity=True,
        enable_verification_checkpoints=True,
        enable_automatic_escalation=True,
        enable_session_persistence=True,
        default_step_timeout_minutes=int(os.getenv("TROUBLESHOOTING_STEP_TIMEOUT", "10")),
        max_session_duration_minutes=int(os.getenv("TROUBLESHOOTING_MAX_DURATION", "60")),
        verification_interval_steps=int(os.getenv("TROUBLESHOOTING_VERIFICATION_INTERVAL", "3")),
        emotional_adaptation_enabled=True,
        technical_level_adaptation=True,
        integrate_with_reasoning_engine=True,
        debug_mode=bool(os.getenv("TROUBLESHOOTING_DEBUG", "false").lower() == "true")
    )
    
    # Initialize troubleshooting engine
    troubleshooting_engine = TroubleshootingEngine(troubleshooting_config)
    
    # Initialize session manager
    session_manager = TroubleshootingSessionManager(troubleshooting_config)
    
    logger.info("Agent Sparrow troubleshooting system initialized successfully")
    
except Exception as e:
    logger.exception("Error during troubleshooting system initialization: %s", e)
    # Initialize fallback None values to prevent errors
    troubleshooting_engine = None
    session_manager = None
    logger.warning("Continuing with troubleshooting system disabled")

logger.info("Module initialization complete.")

# 3. Create the agent logic
async def run_primary_agent(state: PrimaryAgentState) -> AsyncIterator[AIMessageChunk]:
    """
    Asynchronously processes a user query using the primary agent system, yielding AI message chunks as a streaming response.
    
    This function orchestrates advanced reasoning, structured troubleshooting, internal knowledge base search, and web search to generate a comprehensive answer to Mailbird-related queries. It integrates Agent Sparrow's reasoning and troubleshooting engines, dynamically assembles context from multiple sources, constructs a modular system prompt, and streams the AI's response in real time. Extensive telemetry and error handling ensure robust operation and detailed observability.
    
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
                # Yield a single error message chunk and return
                yield AIMessageChunk(content="Your query is too long. Please shorten it and try again.", role="assistant") # Add role
                return # Bare return to exit the async generator

            parent_span.set_attribute("input.query", user_query)
            parent_span.set_attribute("state.message_count", len(state.messages))

            # Agent Sparrow Advanced Reasoning
            reasoning_state = None
            with tracer.start_as_current_span("agent_sparrow.reasoning") as reasoning_span:
                try:
                    # Initialize reasoning engine
                    reasoning_config = ReasoningConfig(
                        enable_chain_of_thought=True,
                        enable_problem_solving_framework=True,
                        enable_tool_intelligence=True,
                        enable_quality_assessment=True,
                        enable_reasoning_transparency=True,
                        debug_mode=False  # Set to True for development
                    )
                    reasoning_engine = ReasoningEngine(reasoning_config)
                    
                    # Perform comprehensive reasoning about the query
                    reasoning_state = await reasoning_engine.reason_about_query(
                        query=user_query,
                        context={"messages": state.messages},
                        session_id=getattr(state, 'session_id', 'default')
                    )
                    
                    # Log reasoning results
                    reasoning_span.set_attribute("reasoning.confidence", reasoning_state.overall_confidence)
                    reasoning_span.set_attribute("reasoning.emotion", reasoning_state.query_analysis.emotional_state.value)
                    reasoning_span.set_attribute("reasoning.category", reasoning_state.query_analysis.problem_category.value)
                    reasoning_span.set_attribute("reasoning.tool_decision", reasoning_state.tool_reasoning.decision_type.value)
                    reasoning_span.set_attribute("reasoning.processing_time", reasoning_state.total_processing_time)
                    
                    logger.info(f"Agent Sparrow reasoning completed: "
                              f"emotion={reasoning_state.query_analysis.emotional_state.value}, "
                              f"category={reasoning_state.query_analysis.problem_category.value}, "
                              f"confidence={reasoning_state.overall_confidence:.2f}, "
                              f"tool_decision={reasoning_state.tool_reasoning.decision_type.value}")
                              
                except Exception as e:
                    logger.error(f"Agent Sparrow reasoning failed: {e}")
                    reasoning_span.record_exception(e)
                    reasoning_span.set_status(Status(StatusCode.ERROR, f"Reasoning error: {str(e)}"))
                    # Continue with fallback behavior
                    reasoning_state = None

            # Agent Sparrow Structured Troubleshooting Integration
            troubleshooting_state = None
            active_troubleshooting_session = None
            
            if troubleshooting_engine and reasoning_state and reasoning_state.query_analysis:
                with tracer.start_as_current_span("agent_sparrow.troubleshooting") as troubleshooting_span:
                    try:
                        qa = reasoning_state.query_analysis
                        
                        # Check if this is a complex technical issue that would benefit from structured troubleshooting
                        should_use_troubleshooting = (
                            qa.problem_category in [
                                reasoning_state.query_analysis.problem_category.TECHNICAL_ISSUE,
                                reasoning_state.query_analysis.problem_category.ACCOUNT_SETUP,
                                reasoning_state.query_analysis.problem_category.PERFORMANCE_OPTIMIZATION
                            ] and
                            (qa.complexity_score >= 0.5 or qa.urgency_level >= 3 or 
                             len(qa.key_entities) >= 2)
                        )
                        
                        if should_use_troubleshooting:
                            # Initiate structured troubleshooting
                            troubleshooting_state = await troubleshooting_engine.initiate_troubleshooting(
                                query_text=user_query,
                                problem_category=qa.problem_category,
                                customer_emotion=qa.emotional_state,
                                reasoning_state=reasoning_state,
                                session_id=getattr(state, 'session_id', None)
                            )
                            
                            if troubleshooting_state.recommended_workflow:
                                # Start troubleshooting session
                                active_troubleshooting_session = await troubleshooting_engine.start_troubleshooting_session(
                                    troubleshooting_state=troubleshooting_state,
                                    session_id=getattr(state, 'session_id', None)
                                )
                                
                                # Track session with session manager
                                if session_manager:
                                    await session_manager.create_session(
                                        workflow=active_troubleshooting_session.workflow,
                                        customer_emotional_state=qa.emotional_state,
                                        customer_technical_level=active_troubleshooting_session.customer_technical_level,
                                        session_id=active_troubleshooting_session.session_id,
                                        context={
                                            'reasoning_insights': reasoning_state.reasoning_summary,
                                            'solution_candidates': [
                                                {
                                                    'summary': sc.solution_summary,
                                                    'confidence': sc.confidence_score
                                                }
                                                for sc in reasoning_state.solution_candidates
                                            ]
                                        }
                                    )
                                
                                troubleshooting_span.set_attribute("troubleshooting.workflow", troubleshooting_state.recommended_workflow.name)
                                troubleshooting_span.set_attribute("troubleshooting.session_id", active_troubleshooting_session.session_id)
                                troubleshooting_span.set_attribute("troubleshooting.technical_level", active_troubleshooting_session.customer_technical_level)
                                
                                logger.info(f"Initiated structured troubleshooting session {active_troubleshooting_session.session_id} "
                                          f"with workflow: {troubleshooting_state.recommended_workflow.name}")
                            
                        troubleshooting_span.set_attribute("troubleshooting.enabled", should_use_troubleshooting)
                        
                    except Exception as e:
                        logger.error(f"Agent Sparrow troubleshooting initialization failed: {e}")
                        troubleshooting_span.record_exception(e)
                        troubleshooting_span.set_status(Status(StatusCode.ERROR, f"Troubleshooting error: {str(e)}"))
                        # Continue without structured troubleshooting
                        troubleshooting_state = None
                        active_troubleshooting_session = None

            # 1. Internal Knowledge Base Search (PostgreSQL + pgvector)
            context_chunks = []
            best_internal_score = 0.0
            internal_docs_count = 0

            with tracer.start_as_current_span("primary_agent.internal_db_search") as internal_search_span:
                try:
                    internal_docs: List[InternalSearchResult] = find_similar_documents(user_query, top_k=4)
                    internal_docs_count = len(internal_docs)
                    if internal_docs:
                        best_internal_score = internal_docs[0].similarity_score # Assuming results are sorted by score desc
                        for doc in internal_docs:
                            content_to_add = doc.markdown if doc.markdown else doc.content
                            if content_to_add:
                                context_chunks.append(f"Source: Internal KB ({doc.url})\nContent: {content_to_add}")
                    logger.info(f"Internal search found {internal_docs_count} documents. Best score: {best_internal_score:.4f}")
                except Exception as e:
                    logger.error(f"Error during internal knowledge base search: {e}")
                    internal_search_span.record_exception(e)
                    internal_search_span.set_status(Status(StatusCode.ERROR, f"Internal DB search failed: {e}"))
                
                internal_search_span.set_attribute("internal_search.document_count", internal_docs_count)
                if internal_docs_count > 0:
                    internal_search_span.set_attribute("internal_search.top_score", best_internal_score)

            # 2. Enhanced tool decision using Agent Sparrow reasoning
            should_web_search = False
            web_search_reasoning = "Legacy fallback logic"
            
            if reasoning_state and reasoning_state.tool_reasoning:
                # Use Agent Sparrow intelligent tool decision
                from app.agents_v2.primary_agent.reasoning.schemas import ToolDecisionType
                
                tool_decision = reasoning_state.tool_reasoning.decision_type
                web_search_reasoning = reasoning_state.tool_reasoning.reasoning
                
                if tool_decision in [ToolDecisionType.WEB_SEARCH_REQUIRED, ToolDecisionType.BOTH_SOURCES_NEEDED]:
                    should_web_search = True
                    logger.info(f"Agent Sparrow reasoning recommends web search: {web_search_reasoning}")
                elif tool_decision == ToolDecisionType.INTERNAL_KB_ONLY:
                    should_web_search = False
                    logger.info(f"Agent Sparrow reasoning recommends internal KB only: {web_search_reasoning}")
                elif tool_decision == ToolDecisionType.NO_TOOLS_NEEDED:
                    should_web_search = False
                    logger.info(f"Agent Sparrow reasoning: no additional tools needed: {web_search_reasoning}")
                else:
                    # Fallback to legacy logic for escalation or unknown decisions
                    should_web_search = True
                    logger.info(f"Agent Sparrow reasoning suggests escalation, using web search as fallback")
                    
                parent_span.set_attribute("tool_decision.reasoning", web_search_reasoning)
                parent_span.set_attribute("tool_decision.type", tool_decision.value)
                parent_span.set_attribute("tool_decision.confidence", reasoning_state.tool_reasoning.confidence)
                
            else:
                # Fallback to legacy logic if reasoning failed
                if internal_docs_count == 0:
                    should_web_search = True
                    web_search_reasoning = "No internal results found, proceeding to web search."
                    logger.info(web_search_reasoning)
                elif best_internal_score < INTERNAL_SEARCH_SIMILARITY_THRESHOLD:
                    should_web_search = True
                    web_search_reasoning = f"Best internal score {best_internal_score:.4f} < {INTERNAL_SEARCH_SIMILARITY_THRESHOLD}, proceeding to web search."
                    logger.info(web_search_reasoning)
                elif internal_docs_count < MIN_INTERNAL_RESULTS_FOR_NO_WEB_SEARCH:
                    should_web_search = True
                    web_search_reasoning = f"Number of internal results {internal_docs_count} < {MIN_INTERNAL_RESULTS_FOR_NO_WEB_SEARCH}, proceeding to web search."
                    logger.info(web_search_reasoning)
                else:
                    web_search_reasoning = "Sufficient internal knowledge available, skipping web search."
                    logger.info(web_search_reasoning)

            if should_web_search:
                with tracer.start_as_current_span("primary_agent.web_search") as web_span:
                    web_span.set_attribute("web.query", user_query)
                    # The official TavilySearchTool returns a list of dictionaries, so we process the results accordingly.
                    if tavily_web_search:
                        try:
                            web_search_results = tavily_web_search.invoke({"query": user_query})

                            if isinstance(web_search_results, list) and web_search_results:
                                web_urls_found = [result.get("url") for result in web_search_results if result.get("url")]
                                web_snippets_added = 0
                                for result in web_search_results:
                                    url = result.get("url")
                                    content_snippet = result.get("content", "")
                                    if url and content_snippet:
                                        # Prioritize adding web search snippets if available
                                        context_chunks.append(f"Source: Web Search ({url})\nContent: {content_snippet}")
                                        web_snippets_added += 1
                                if web_snippets_added > 0:
                                    web_span.set_attribute("web.results_count", web_snippets_added)
                                    logger.info(f"Web search added {web_snippets_added} content snippets to context.")
                                else:
                                    web_span.set_attribute("web.results_count", 0)
                                    logger.info("Web search executed but returned no usable content snippets (URL + content).")
                            elif isinstance(web_search_results, list) and not web_search_results:
                                logger.info("Web search executed but returned no results.")
                                web_span.set_attribute("web.results_count", 0)
                            else:
                                logger.error(f"Tavily web search returned an unexpected result (not a list): {web_search_results}")
                                web_span.set_attribute("web.error", f"Unexpected Tavily result: {type(web_search_results).__name__}")
                        except Exception as e:
                            logger.error(f"Error during web search execution: {e}")
                            web_span.record_exception(e)
                            web_span.set_status(Status(StatusCode.ERROR, f"Web search execution failed: {e}"))
                    else:
                        logger.warning("Web search fallback triggered, but Tavily tool is not available.")
                        web_span.set_attribute("web.tool_available", False)

    # Build prompt with context
            # If a previous reflection suggested corrections, incorporate them
            correction_note = ""
            if getattr(state, "reflection_feedback", None) and state.reflection_feedback.correction_suggestions:
                correction_note = (
                    "\nPlease address the following feedback to improve your answer: "
                    f"{state.reflection_feedback.correction_suggestions}\n"
                )

            # Build context_text, ensuring not to exceed the character limit
            # We'll give some preference to web search results if they exist by adding them first to a temporary list
            # This is a simple way to ensure they are less likely to be truncated if KB content is very long.
            # A more sophisticated approach might involve token counting and smarter selection.
            
            temp_context_parts = []
            # Add web search results first if they were intended to be used
            if should_web_search:
                for chunk in context_chunks:
                    if "Source: Web Search" in chunk:
                        temp_context_parts.append(chunk)
            
            # Then add internal KB results
            for chunk in context_chunks:
                if "Source: Internal KB" in chunk:
                    temp_context_parts.append(chunk)

            # Join and truncate
            full_context_str = "\n\n".join(temp_context_parts) # Use double newline for better separation
            if len(full_context_str) > 3500:
                logger.warning(f"Combined context length ({len(full_context_str)}) exceeds 3500 chars. Truncating.")
                context_text = full_context_str[:3500]
            else:
                context_text = full_context_str
            logger.info(f"Final context_text length: {len(context_text)}")

            # Load Agent Sparrow prompt using modular system
            with tracer.start_as_current_span("agent_sparrow.load_prompt") as prompt_span:
                # Detect customer emotion from the query
                current_message = state.messages[-1].content if state.messages else ""
                emotion_result = EmotionTemplates.detect_emotion(current_message)
                prompt_span.set_attribute("emotion.detected", emotion_result.primary_emotion.value)
                prompt_span.set_attribute("emotion.confidence", emotion_result.confidence_score)
                
                # Configure Agent Sparrow prompt
                prompt_config = PromptLoadConfig(
                    version=PromptVersion.V3_SPARROW,
                    include_reasoning=True,
                    include_emotions=True,
                    include_technical=True,
                    quality_enforcement=True,
                    debug_mode=False,  # Set to True for development
                    environment="production"
                )
                
                # Load the sophisticated Agent Sparrow system prompt
                agent_sparrow_prompt = load_agent_sparrow_prompt(prompt_config)
                logger.info(f"Loaded Agent Sparrow prompt (emotion: {emotion_result.primary_emotion.value}, confidence: {emotion_result.confidence_score:.2f})")
                
            # Add structured troubleshooting context if active
            troubleshooting_context = ""
            if active_troubleshooting_session:
                troubleshooting_context = f"""
                
## Structured Troubleshooting Active:
**Workflow**: {active_troubleshooting_session.workflow.name}
**Session ID**: {active_troubleshooting_session.session_id}
**Customer Technical Level**: {active_troubleshooting_session.customer_technical_level}/5
**Current Phase**: {active_troubleshooting_session.current_phase.value}

**Current Diagnostic Step**: {active_troubleshooting_session.current_step.title if active_troubleshooting_session.current_step else "Initializing"}

**Approach**: Provide systematic troubleshooting guidance following the structured workflow. 
- Break down complex solutions into step-by-step diagnostic procedures
- Include verification checkpoints to ensure progress
- Adapt complexity to customer technical level
- Monitor for escalation criteria
- Maintain structured approach while being empathetic and supportive

**Workflow Description**: {active_troubleshooting_session.workflow.description}
"""
                
            refined_system_prompt = (
                agent_sparrow_prompt + 
                "\n\n## Context from Knowledge Base and Web Search:\n" +
                f"{context_text}" + 
                troubleshooting_context +
                correction_note
            )
            system_msg = SystemMessage(content=refined_system_prompt)
            # Ensure messages list doesn't grow indefinitely if state is reused across turns in a single graph invocation (though typically not the case for primary agent)
            # For this agent, state.messages usually contains the current user query as the last message.
            # We construct the prompt with the current user query and the new system message.
            current_user_message = state.messages[-1]
            prompt_messages = [system_msg, current_user_message] # System message first, then user query
            logger.info(f"Prompt being sent to LLM: {prompt_messages}") # Log the prompt
            parent_span.add_event("primary_agent.llm_stream_start", {"prompt": str(prompt_messages)})

            try:
                logger.info("Initializing LLM stream iterator...")
                stream_iter = model_with_tools.stream(prompt_messages)
                logger.info("LLM stream iterator initialized. Starting iteration...")
                chunk_count = 0
                while True:
                    logger.debug(f"Attempting to get next chunk (iteration {chunk_count})...")
                    chunk = await anyio.to_thread.run_sync(lambda: next(stream_iter, None))
                    
                    if chunk is None:
                        logger.info(f"LLM stream ended after {chunk_count} chunks.")
                        break
                    
                    chunk_count += 1
                    logger.info(f"Received chunk {chunk_count}. Content: '{chunk.content}' Role: {getattr(chunk, 'role', 'N/A')}")
                    parent_span.add_event("primary_agent.llm_chunk_received", {"chunk_number": chunk_count, "chunk_content_length": len(chunk.content or ""), "chunk_role": getattr(chunk, 'role', 'N/A')})
                    yield chunk
                
                if chunk_count == 0:
                    logger.warning("LLM stream produced 0 chunks.")
                parent_span.set_status(Status(StatusCode.OK))
            except Exception as e:
                error_message = f"I encountered an issue processing your request. Details: {type(e).__name__}"
                if "safety" in str(e).lower() or "blocked" in str(e).lower():
                    error_message = "I'm sorry, I cannot respond to that query due to safety guidelines."
                
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, f"LLM stream error: {str(e)}"))
                yield AIMessageChunk(content=error_message, role="assistant") # Ensure role for error chunks
        except Exception as e: # Outer exception for agent logic errors
            logger.exception("Error in run_primary_agent main logic: %s", e)
            if 'parent_span' in locals():
                parent_span.record_exception(e)
                parent_span.set_status(Status(StatusCode.ERROR, str(e)))
            yield AIMessageChunk(content=f"An internal error occurred: {str(e)}", role="assistant") 