from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.orchestration.orchestration.graph import _route_from_agent
from app.agents.orchestration.orchestration.state import GraphState
from app.agents.orchestration.orchestration.subagent_state import (
    extract_pending_task_calls,
    has_routable_pending_task_calls,
)
from app.agents.unified.agent_sparrow import _determine_task_type


def test_task_type_patterns_are_hint_only_for_web_research() -> None:
    state = GraphState(
        messages=[HumanMessage(content="Can you research latest Mailbird pricing?")],
        forwarded_props={},
    )

    task_type = _determine_task_type(state)

    assert task_type == "coordinator"
    assert state.forwarded_props.get("task_hint") == "web_research"


def test_task_type_patterns_are_hint_only_for_data_retrieval() -> None:
    state = GraphState(
        messages=[HumanMessage(content="Please query the database table for recent account metrics")],
        forwarded_props={},
    )

    task_type = _determine_task_type(state)

    assert task_type == "coordinator"
    assert state.forwarded_props.get("task_hint") == "data_retrieval"


def test_subgraph_route_selected_for_routable_task_call() -> None:
    state = GraphState(
        messages=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_123",
                        "name": "task",
                        "args": {
                            "description": "Research known auth issues",
                            "subagent_type": "research-agent",
                        },
                    }
                ],
            )
        ],
    )

    assert has_routable_pending_task_calls(state) is True
    assert _route_from_agent(state) == "subgraphs"



def test_pending_task_extraction_respects_executed_tool_calls() -> None:
    state = GraphState(
        messages=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_done",
                        "name": "task",
                        "args": {
                            "description": "Analyze data",
                            "subagent_type": "data-analyst",
                        },
                    },
                    {
                        "id": "call_pending",
                        "name": "task",
                        "args": {
                            "description": "Draft response",
                            "subagent_type": "draft-writer",
                        },
                    },
                ],
            )
        ],
        scratchpad={"_system": {"_executed_tool_calls": ["call_done"]}},
    )

    pending = extract_pending_task_calls(state)

    assert [call.tool_call_id for call in pending] == ["call_pending"]
    assert pending[0].subagent_type == "draft-writer"
