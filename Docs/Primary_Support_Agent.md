# Primary Support Agent Technical Documentation

## 1. Overview

The Primary Support Agent is a core component of the MB-Sparrow multi-agent system. It is designed to handle general user queries related to the Mailbird desktop email client. It leverages a knowledge base, web search capabilities, and a powerful language model to provide relevant and helpful responses.

## 2. Functionality

The agent follows a specific workflow to process user queries:

1.  **Query Reception**: Receives the user's query, typically as the latest message in a conversation history.
2.  **Knowledge Base (KB) Retrieval**: Performs a similarity search against the Supabase PostgreSQL database (using the `pgvector` extension and the `mailbird_knowledge` table) via the `find_similar_documents` function from `app.db.embedding_utils.py`. It retrieves the top relevant documents based on cosine similarity.
3.  **Relevance Check & Web Search Decision**: The agent decides whether to perform a web search using the Tavily API based on the results from the internal KB search. A web search is triggered if:
    *   No relevant documents are found in the internal KB.
    *   The similarity score of the best-matching internal document is below `INTERNAL_SEARCH_SIMILARITY_THRESHOLD` (default: 0.75).
    *   The number of relevant internal documents found is less than `MIN_INTERNAL_RESULTS_FOR_NO_WEB_SEARCH` (default: 2).
4.  **Context Aggregation**: Combines the content from the retrieved KB documents and (if applicable) web search results to form a comprehensive context.
5.  **Prompt Engineering**: Constructs a prompt for the language model (Google Gemini 2.5 Flash) that includes:
    *   A detailed system message defining its role as a Mailbird support assistant, desired tone, and operational guidelines (including safety).
    *   The aggregated context.
    *   The user's original query.
6.  **Language Model Invocation**: Invokes the language model with the prepared prompt and bound tools (`mailbird_kb_search`, `tavily_web_search`). The model interaction is configured for streaming responses.
7.  **Response Streaming**: Returns the language model's response as a stream of `AIMessageChunk` objects.

## 3. Key Files and Modules

*   **`agent.py`**: Contains the main logic for the agent.
    *   Initializes the Google Gemini language model with specific safety settings and tool bindings (e.g., `tavily_web_search`).
    *   Uses `app.db.embedding_utils.py` (which handles Supabase connection and `pgvector` operations) for knowledge base interactions.
    *   Defines the `run_primary_agent` function, which orchestrates the agent's workflow, including calling `find_similar_documents` for KB retrieval.
*   **`tools.py`**: Defines the tools available to the language model:
    *   `mailbird_kb_search`: Note: Internal knowledge base search is currently performed directly by the `run_primary_agent` function using `find_similar_documents` before the main LLM call. A dedicated `mailbird_kb_search` tool is not actively bound or used by the LLM in the current implementation for re-querying.
    *   `tavily_web_search`: A `StructuredTool` that allows the agent to perform web searches via the Tavily API.
*   **`schemas.py`**: Defines the Pydantic model for the agent's state:
    *   `PrimaryAgentState`: Holds the conversation history (`messages: List[BaseMessage]`).

## 4. Configuration

The agent relies on several environment variables for its operation:

*   `GEMINI_API_KEY`: API key for Google Gemini services.
*   `DATABASE_URL`: PostgreSQL connection string for Supabase (e.g., `postgresql://user:password@host:port/dbname`). This is used by `app.db.embedding_utils.py`.
*   `TAVILY_API_KEY`: API key for the Tavily web search service.
*   `INTERNAL_SEARCH_SIMILARITY_THRESHOLD`: Float value (0.0 to 1.0, default: `0.75`). If the best internal search result's similarity score (cosine similarity, higher is better) is below this, a web search may be triggered.
*   `MIN_INTERNAL_RESULTS_FOR_NO_WEB_SEARCH`: Integer (default: `2`). If fewer than this many relevant internal results are found, a web search may be triggered.

### Safety Settings

The Google Gemini model is initialized with the following safety settings, configured to block content rated `MEDIUM` or higher for these categories:
*   `HARM_CATEGORY_HARASSMENT`
*   `HARM_CATEGORY_HATE_SPEECH`
*   `HARM_CATEGORY_SEXUALLY_EXPLICIT`
*   `HARM_CATEGORY_DANGEROUS_CONTENT`

## 5. Core Features

*   **Streaming Responses**: The `run_primary_agent` function is designed to stream responses from the language model, allowing for faster perceived performance and real-time output to the user.
*   **Telemetry & Observability**: Integrated with OpenTelemetry. The `run_primary_agent` function creates spans for its main execution, internal knowledge base retrieval (Supabase/pgvector queries via `find_similar_documents`), web searches, and LLM interaction, providing detailed traces for monitoring and debugging.
*   **Safety Guardrails**:
    *   **Model-Level**: Utilizes Google Gemini's built-in safety filters (configured as described above).
    *   **Input Validation**: Basic validation for query length (max 4000 characters).
    *   **System Prompt**: The system prompt guides the LLM to stay on topic, maintain a polite tone, and avoid harmful content.
    *   **Error Handling**: Basic error handling for LLM stream issues, providing a user-friendly message if responses are potentially blocked or an error occurs.

## 6. Usage and Integration

The `run_primary_agent` function is designed to be a node within a LangGraph orchestration graph. It expects an input state of type `PrimaryAgentState` and returns a dictionary with a `"messages"` key, containing an iterator of `AIMessageChunk` objects representing the streamed response.

Example of expected input structure for the graph (simplified for `run_primary_agent`):
```python
{
    "messages": [HumanMessage(content="User's query about Mailbird")]
}
```

Example of output structure from `run_primary_agent`:
```python
{
    "messages": <iterator yielding AIMessageChunk objects>
}
```

This agent forms a crucial part of the conversational AI system, providing the primary interface for user support queries.
