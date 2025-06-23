"""Unit tests for the intelligent query router node.

These tests mock the LangChain Expression Language (LCEL) chain
so no external calls are made.
"""
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable

from app.agents_v2.orchestration.state import GraphState
from app.agents_v2.router import router as router_module
from app.agents_v2.router.schemas import RouteQueryWithConf


@pytest.fixture
def mock_router_chain() -> MagicMock:
    """
    Mocks the entire router chain created by `router_prompt | structured_llm`.
    This is more robust than mocking the LLM, as it's not tied to the
    implementation detail of using the `|` operator.
    """
    # By patching the `__or__` method of the prompt template, we can intercept
    # the creation of the chain and substitute our own mock chain.
    with patch("langchain_core.prompts.chat.ChatPromptTemplate.__or__") as mock_or:
        mock_chain = MagicMock(spec=Runnable)
        mock_or.return_value = mock_chain
        yield mock_chain


@pytest.mark.parametrize(
    "destination,confidence,expected",
    [
        ("primary_agent", 0.95, "primary_agent"),  # high-conf primary_agent
        ("log_analyst", 0.88, "log_analyst"),      # high-conf log_analyst
        ("researcher", 0.20, "primary_agent"),     # low confidence should fallback
    ],
)
def test_router_destinations(
    mock_router_chain: MagicMock, destination: str, confidence: float, expected: str
):
    """Ensure router chooses correct destination or falls back when confidence low."""
    mock_router_chain.invoke.return_value = RouteQueryWithConf(
        destination=destination, confidence=confidence
    )

    state = GraphState(messages=[HumanMessage(content="Test query")])
    result = router_module.query_router(state)

    assert result["destination"] == expected
    mock_router_chain.invoke.assert_called_once_with({"query": "Test query"})


def test_router_llm_exception(mock_router_chain: MagicMock):
    """LLM errors should trigger fallback to primary_agent."""
    mock_router_chain.invoke.side_effect = RuntimeError("simulated llm failure")

    state = GraphState(messages=[HumanMessage(content="Test query")])
    result = router_module.query_router(state)
    assert result["destination"] == "primary_agent"
