import pytest
from unittest.mock import patch, MagicMock
from langchain_core.runnables import Runnable

from app.agents_v2.router.router import query_router
from app.agents_v2.router.schemas import RouteQueryWithConf


@pytest.fixture
def mock_router_chain():
    """
    Mocks the entire router chain created by `router_prompt | structured_llm`.
    This is more robust than mocking the LLM, as it's not tied to the
    implementation detail of using the `|` operator.
    """
    # By patching the `__or__` method of the prompt template, we can intercept
    # the creation of the chain and substitute our own mock chain.
    with patch('langchain_core.prompts.chat.ChatPromptTemplate.__or__') as mock_or:
        mock_chain = MagicMock(spec=Runnable)
        mock_or.return_value = mock_chain
        yield mock_chain


@pytest.mark.parametrize(
    "user_query, expected_destination",
    [
        ("What is the latest version of Mailbird?", "primary_agent"),
        ("I am seeing a lot of errors in the logs.", "log_analyst"),
        ("What are the best practices for email marketing?", "researcher"),
        ("My app is crashing, can you check the logs?", "log_analyst"),
        ("Tell me about the features of Mailbird?", "primary_agent"),
        ("Search for information about AI in email clients.", "researcher"),
    ],
)
def test_query_router(mock_router_chain, user_query, expected_destination):
    """
    Test that the query_router correctly routes queries based on user input.
    """
    # Arrange
    # The mocked chain should return an instance of the RouteQueryWithConf Pydantic model.
    mock_router_chain.invoke.return_value = RouteQueryWithConf(
        destination=expected_destination, confidence=0.9
    )

    # The state should be a dictionary that can be parsed into GraphState
    state = {"messages": [("user", user_query)]}

    # Act
    result_dict = query_router(state)

    # Assert
    assert "destination" in result_dict
    assert result_dict["destination"] == expected_destination
    # The chain is invoked with the input for the prompt
    mock_router_chain.invoke.assert_called_once_with({"query": user_query})
 