from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.api.v1.endpoints import agui_endpoints
from app.agents.unified import provider_factory


class _TestSettings:
    enable_grounding_search = True
    langsmith_tracing_enabled = False
    langsmith_project = None
    langsmith_endpoint = None
    agent_memory_default_enabled = False

    @staticmethod
    def should_enable_agent_memory() -> bool:
        return False


class _FakeModel:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[tuple[list[object], dict | None]] = []

    async def ainvoke(self, messages, config=None):
        self.calls.append((list(messages), config))
        return AIMessage(content=self.response_text)


@pytest.mark.asyncio
async def test_degraded_fallback_is_mode_aware_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = _FakeModel(
        ":::thinking\ninternal only\n:::\nFinal answer for the user."
    )

    def _fake_build_chat_model(provider: str, model: str, role: str):
        assert provider == "google"
        assert model == "gemini-3-flash-preview"
        assert role == "coordinator"
        return fake_model

    monkeypatch.setattr(provider_factory, "build_chat_model", _fake_build_chat_model)

    result = await agui_endpoints._degraded_direct_response_fallback(
        provider="google",
        model="gemini-3-flash-preview",
        user_query="Give me a short answer",
        agent_mode="creative_expert",
    )

    assert result == "Final answer for the user."
    assert fake_model.calls
    sent_messages = fake_model.calls[0][0]
    assert isinstance(sent_messages[0], SystemMessage)
    assert "creative specialist" in str(sent_messages[0].content).lower()
    assert "production support incident" not in str(sent_messages[0].content).lower()
    assert isinstance(sent_messages[1], HumanMessage)


def test_merge_agui_context_prefers_explicit_mode_over_legacy_agent_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agui_endpoints, "get_settings", lambda: _TestSettings())

    properties = {
        "session_id": "s-1",
        "provider": "google",
        "model": "gemini-3-flash-preview",
        "agent_type": "log_analysis",
        "agent_mode": "creative_expert",
    }
    state: dict = {}
    config: dict = {"configurable": {}}

    agui_endpoints._merge_agui_context(properties, state, config)

    configurable = config["configurable"]
    assert configurable["agent_type"] == "log_analysis"
    assert configurable["agent_mode"] == "creative_expert"
    assert state["agent_mode"] == "creative_expert"
    assert configurable["metadata"]["agent_config"]["agent_mode"] == "creative_expert"


def test_merge_agui_context_maps_legacy_agent_type_when_mode_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agui_endpoints, "get_settings", lambda: _TestSettings())

    properties = {
        "session_id": "s-2",
        "provider": "google",
        "model": "gemini-3-flash-preview",
        "agent_type": "log_analysis",
    }
    state: dict = {}
    config: dict = {"configurable": {}}

    agui_endpoints._merge_agui_context(properties, state, config)

    configurable = config["configurable"]
    assert configurable["agent_mode"] == "mailbird_expert"
    assert state["agent_mode"] == "mailbird_expert"
    assert configurable["metadata"]["agent_config"]["agent_mode"] == "mailbird_expert"
