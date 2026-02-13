from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

import app.agents.unified.agent_sparrow as sparrow
import app.agents.unified.tools as tools_module
from app.agents.orchestration.orchestration.state import Attachment, GraphState
from app.agents.unified.prompts import (
    DATA_ANALYST_PROMPT,
    DATABASE_RETRIEVAL_PROMPT,
    DRAFT_WRITER_PROMPT,
    EXPLORER_PROMPT,
    LOG_ANALYSIS_PROMPT,
    NINE_STEP_REASONING_BASE,
    RESEARCH_PROMPT,
    get_coordinator_prompt,
)
from app.agents.unified.tools import get_registered_tools_for_mode


def _tool_names(mode: str) -> set[str]:
    return {tool.name for tool in get_registered_tools_for_mode(mode)}


def test_coordinator_prompt_general_mode_uses_canonical_base_without_mailbird_restriction() -> None:
    prompt = get_coordinator_prompt(
        model="gemini-3-flash-preview",
        provider="google",
        include_skills=False,
        current_date="2026-02-13",
        zendesk=False,
        agent_mode="general",
    )
    assert "You are a very strong reasoner and planner." in prompt
    assert "Mode: General Assistant." in prompt
    assert "Mode: Mailbird Expert." not in prompt
    assert "seasoned Mailbird technical support expert" not in prompt


@pytest.mark.parametrize(
    ("mode", "expected_role"),
    [
        ("mailbird_expert", "Mode: Mailbird Expert."),
        ("research_expert", "Mode: Research Expert."),
        ("creative_expert", "Mode: Creative Expert."),
    ],
)
def test_coordinator_prompt_injects_mode_specific_role(mode: str, expected_role: str) -> None:
    prompt = get_coordinator_prompt(
        model="gemini-3-flash-preview",
        provider="google",
        include_skills=False,
        current_date="2026-02-13",
        zendesk=False,
        agent_mode=mode,
    )
    assert expected_role in prompt
    assert "You are a very strong reasoner and planner." in prompt


def test_all_subagent_prompts_include_canonical_nine_step_base() -> None:
    canonical_header = "You are a very strong reasoner and planner."
    prompts = [
        LOG_ANALYSIS_PROMPT,
        RESEARCH_PROMPT,
        EXPLORER_PROMPT,
        DATABASE_RETRIEVAL_PROMPT,
        DRAFT_WRITER_PROMPT,
        DATA_ANALYST_PROMPT,
    ]
    for prompt in prompts:
        assert canonical_header in prompt
        assert NINE_STEP_REASONING_BASE.splitlines()[0] in prompt


def test_tool_registry_mode_scoping_and_image_registration() -> None:
    general_tools = _tool_names("general")
    mailbird_tools = _tool_names("mailbird_expert")
    research_tools = _tool_names("research_expert")
    creative_tools = _tool_names("creative_expert")

    assert "generate_image" in general_tools
    assert "generate_image" in mailbird_tools
    assert "generate_image" in research_tools
    assert "generate_image" in creative_tools
    assert "log_diagnoser" in mailbird_tools


def test_skills_context_uses_dynamic_auto_detection_for_non_zendesk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRegistry:
        def __init__(self) -> None:
            self.context_calls = 0
            self.default_calls = 0

        def get_context_skills_content(self, context):  # noqa: ANN001
            self.context_calls += 1
            return "dynamic-skill-content"

        def get_default_skills_content(self, context):  # noqa: ANN001
            self.default_calls += 1
            return "default-skill-content"

    fake_registry = _FakeRegistry()
    monkeypatch.setattr(sparrow, "get_skills_registry", lambda: fake_registry)

    state = GraphState(
        messages=[HumanMessage(content="Please write and polish this draft.")],
        forwarded_props={"is_zendesk_ticket": False},
    )

    content = sparrow._build_skills_context(state, runtime=SimpleNamespace())

    assert content == "dynamic-skill-content"
    assert fake_registry.context_calls == 1
    assert fake_registry.default_calls == 0


def test_determine_task_type_respects_hard_mode_switch_for_explicit_log_override() -> None:
    blocked_state = GraphState(
        messages=[HumanMessage(content="Please inspect this log")],
        forwarded_props={
            "agent_mode": "creative_expert",
            "agent_type": "log_analysis",
        },
    )
    blocked = sparrow._determine_task_type(blocked_state)
    assert blocked == "coordinator"
    assert blocked_state.agent_mode == "creative_expert"
    assert blocked_state.agent_type is None
    assert "agent_type" not in (blocked_state.forwarded_props or {})

    allowed_state = GraphState(
        messages=[HumanMessage(content="Please inspect this log")],
        forwarded_props={
            "agent_mode": "research_expert",
            "agent_type": "log_analysis",
        },
    )
    allowed = sparrow._determine_task_type(allowed_state)
    assert allowed == "log_analysis"
    assert allowed_state.agent_mode == "research_expert"
    assert allowed_state.agent_type == "log_analysis"


def test_determine_task_type_keeps_mode_and_uses_log_hint_for_attachments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sparrow,
        "_attachments_indicate_logs",
        lambda _state: {
            "has_log": True,
            "candidates": [{"name": "app.log"}],
            "non_text_skipped": [],
        },
    )
    state = GraphState(
        messages=[HumanMessage(content="Can you investigate?")],
        attachments=[
            Attachment(
                name="app.log",
                mime_type="text/plain",
                data_url="data:text/plain;base64,ZXJyb3I=",
                size=5,
            )
        ],
        forwarded_props={"agent_mode": "general"},
    )

    task_type = sparrow._determine_task_type(state)
    assert task_type == "coordinator"
    assert state.agent_mode == "general"
    assert state.agent_type is None
    assert (state.forwarded_props or {}).get("task_hint") == "log_analysis"
    assert (state.forwarded_props or {}).get("task_detection_method") == "attachment"


@pytest.mark.asyncio
async def test_autoroute_log_analysis_respects_mode_and_does_not_switch_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sparrow,
        "_attachments_indicate_logs",
        lambda _state: {
            "has_log": True,
            "candidates": [{"name": "app.log"}],
            "non_text_skipped": [],
        },
    )

    blocked_state = GraphState(
        messages=[HumanMessage(content="Please inspect this file")],
        forwarded_props={"agent_mode": "creative_expert"},
    )
    blocked = await sparrow._maybe_autoroute_log_analysis(
        blocked_state, helper=SimpleNamespace()
    )
    assert blocked is None
    assert blocked_state.agent_type is None

    allowed_state = GraphState(
        messages=[HumanMessage(content="Please inspect this file")],
        forwarded_props={"agent_mode": "general"},
    )
    allowed = await sparrow._maybe_autoroute_log_analysis(
        allowed_state, helper=SimpleNamespace()
    )
    assert isinstance(allowed, SystemMessage)
    assert "log_diagnoser" in str(allowed.content)
    assert allowed_state.agent_type is None
    assert (allowed_state.forwarded_props or {}).get("task_hint") == "log_analysis"


def test_tool_registry_includes_minimax_tools_only_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_minimax_tool = SimpleNamespace(name="minimax_web_search")

    monkeypatch.setattr(tools_module, "is_minimax_available", lambda: True)
    monkeypatch.setattr(
        tools_module, "get_minimax_tools", lambda: [fake_minimax_tool]
    )
    with_minimax = {tool.name for tool in get_registered_tools_for_mode("general")}
    assert "minimax_web_search" in with_minimax

    monkeypatch.setattr(tools_module, "is_minimax_available", lambda: False)
    without_minimax = {tool.name for tool in get_registered_tools_for_mode("general")}
    assert "minimax_web_search" not in without_minimax
