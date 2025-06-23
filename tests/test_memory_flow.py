"""Integration-ish test ensuring pre_process caches and Qdrant flow.
Uses monkeypatch to stub external network dependencies.
"""
from __future__ import annotations

import types
from types import SimpleNamespace
import os

from langchain_core.documents import Document
from app.agents_v2.orchestration.graph import workflow
from unittest.mock import patch, MagicMock

from langchain_core.messages import HumanMessage

def test_cached_flow(monkeypatch):
    """Cache hit → return cached response immediately."""
    from app.agents_v2.orchestration.graph import app as compiled_graph
    # Patch RedisCache.get to always hit
    monkeypatch.setattr(
        "app.agents_v2.orchestration.nodes.cache_layer.get", lambda q: "cached resp"
    )
    # Ensure Qdrant not called
    monkeypatch.setattr(
        "app.agents_v2.orchestration.nodes.vector_memory.retrieve_context", lambda *a, **k: []
    )

    input_state = {"session_id": "s1", "messages": [HumanMessage(content="Hello?")]}
    final_state = compiled_graph.invoke(input_state)

    # The graph should end, and the final state should contain the cached response.
    assert final_state["cached_response"] == "cached resp"


def test_vector_flow(monkeypatch):
    """No cache hit → context retrieval path."""
    # 1. Create a mock for the QdrantMemory service instance.
    mock_vector_memory = MagicMock()
    # 2. Configure its retrieve_context method to return a known value.
    mock_vector_memory.retrieve_context.return_value = [Document(page_content="ctx1")]

    # 3. Use monkeypatch to replace the *instance* in the nodes module.
    #    This must happen BEFORE the graph is imported and invoked.
    monkeypatch.setattr("app.agents_v2.orchestration.nodes.vector_memory", mock_vector_memory)

    # 4. Now, import the graph. The pre-existing `vector_memory` instance is replaced.
    from app.agents_v2.orchestration.graph import app as compiled_graph

    # 5. Ensure cache misses to trigger the vector search path.
    monkeypatch.setattr("app.agents_v2.orchestration.nodes.cache_layer.get", lambda q: None)

    # 6. Prepare input state.
    input_state = {"session_id": "s1", "messages": [HumanMessage(content="Hello?")]}

    # 7. Act.
    final_state = compiled_graph.invoke(input_state)

    # 8. Assert.
    # Check that our mock was called.
    mock_vector_memory.retrieve_context.assert_called_once_with(query="Hello?")
    # Check that the context from our mock was added to the state.
    assert "ctx1" in final_state["context"] 
    assert isinstance(final_state["context"], list)
    assert len(final_state["context"]) == 1
    assert isinstance(final_state["context"][0], Document)
    assert final_state["context"][0].page_content == "ctx1"
