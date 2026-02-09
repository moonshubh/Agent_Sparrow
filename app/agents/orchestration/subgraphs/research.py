"""Research subgraph builder."""

from __future__ import annotations

from ._base import build_subagent_runner


def build_research_subgraph():
    return build_subagent_runner(subagent_name="research-agent", subgraph_name="research")
