import pytest
import os
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessageChunk, SystemMessage
from app.db.embedding_utils import SearchResult as InternalSearchResult

from app.agents_v2.primary_agent.schemas import PrimaryAgentState

# Fixture to set necessary environment variables for all tests in this file
@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_api_key")
    monkeypatch.setenv("TAVILY_API_KEY", "test_tavily_api_key")
    monkeypatch.setenv("KB_RELEVANCE_THRESHOLD", "0.5")
    # Set fallback logic env vars for predictable testing
    monkeypatch.setenv("INTERNAL_SEARCH_SIMILARITY_THRESHOLD", "0.75")
    monkeypatch.setenv("MIN_INTERNAL_RESULTS_FOR_NO_WEB_SEARCH", "2")


# Fixture to provide a mock for the Tavily web search tool
@pytest.fixture
def mock_tavily_search():
    # Patch the function in the agent's namespace where it's imported and used
    with patch('app.agents_v2.primary_agent.agent.tavily_web_search') as mock_search:
        mock_search.invoke.return_value = {"urls": ["http://web.example.com/result", "Mocked Tavily URL 2"]}
        yield mock_search

# Fixture to provide a mock for the primary agent's LLM
@pytest.fixture
def mock_primary_llm():
    # Patch the model_with_tools object directly, as it's created at module load time.
    # This prevents real API calls to Google.
    with patch('app.agents_v2.primary_agent.agent.model_with_tools') as mock_model_with_tools:
        # The actual mock for the .stream() method, which is what the agent calls.
        mock_stream_method = MagicMock(return_value=iter([AIMessageChunk(content="Mocked LLM response")]))
        mock_model_with_tools.stream = mock_stream_method
        # Yield the mock for the .stream() method so we can assert calls to it.
        yield mock_stream_method

# Test case: KB search finds relevant documents, so web search should NOT be called.
@patch('app.agents_v2.primary_agent.agent.find_similar_documents')
def test_primary_agent_with_kb_docs_no_web_search(
    mock_find_docs,
    mock_tavily_search, # This is the patched function object
    mock_primary_llm    # This is the mock for the .stream() method
):
    """
    Test that run_primary_agent does NOT call web search when find_similar_documents
    returns relevant results.
    """
    # Arrange
    from app.agents_v2.primary_agent.agent import run_primary_agent

    # 1. Configure find_similar_documents to return relevant docs (at least 2 to avoid fallback)
    # Use InternalSearchResult to match the actual return type of the function.
    mock_find_docs.return_value = [
        InternalSearchResult(id=1, url="url1", markdown="Relevant KB document content 1.", content="", metadata={}, similarity_score=0.9),
        InternalSearchResult(id=2, url="url2", markdown="Relevant KB document content 2.", content="", metadata={}, similarity_score=0.8)
    ]

    # 2. Set up the initial state
    initial_messages = [HumanMessage(content="User query with good KB hit")]
    state = PrimaryAgentState(messages=initial_messages)

    # Act
    result = run_primary_agent(state)
    
    # Consume the generator to trigger assertions on mocks
    list(result["messages"])

    # Assert
    # 1. KB search was called
    mock_find_docs.assert_called_once_with("User query with good KB hit", top_k=4)
    
    # 2. Web search was NOT called
    mock_tavily_search.assert_not_called()
    
    # 3. LLM was called with context from KB search
    llm_input_messages = mock_primary_llm.call_args[0][0]
    system_message_content = next(m.content for m in llm_input_messages if isinstance(m, SystemMessage))
    
    assert "Relevant KB document content 1." in system_message_content
    assert "Source: Web Search Results" not in system_message_content

# Test case: KB search finds no documents, so web search SHOULD be called.
@patch('app.agents_v2.primary_agent.agent.find_similar_documents')
def test_primary_agent_no_kb_docs_triggers_web_search(
    mock_find_docs,
    mock_tavily_search,
    mock_primary_llm
):
    """
    Test that run_primary_agent calls web search when find_similar_documents
    returns no results.
    """
    # Arrange
    from app.agents_v2.primary_agent.agent import run_primary_agent

    # 1. Configure find_similar_documents to return no results
    mock_find_docs.return_value = []

    # 2. Set up the initial state
    initial_messages = [HumanMessage(content="User query with no KB hit")]
    state = PrimaryAgentState(messages=initial_messages)

    # Act
    result = run_primary_agent(state)
    
    # Consume the generator to trigger assertions on mocks
    list(result["messages"])

    # Assert
    # 1. KB search was called
    mock_find_docs.assert_called_once_with("User query with no KB hit", top_k=4)

    # 2. Web search WAS called
    mock_tavily_search.invoke.assert_called_once_with({"query": "User query with no KB hit", "max_results": 3})

    # 3. LLM was called with context from web search
    llm_input_messages = mock_primary_llm.call_args[0][0]
    system_message_content = next(m.content for m in llm_input_messages if isinstance(m, SystemMessage))

    assert "internal knowledge base results" not in system_message_content.lower()
    assert "http://web.example.com/result" in system_message_content
