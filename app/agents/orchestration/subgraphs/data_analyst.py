"""Data analyst subgraph builder."""

from __future__ import annotations

from ._base import SubgraphRunner, build_subagent_runner


def build_data_analyst_subgraph() -> SubgraphRunner:
    return build_subagent_runner(
        subagent_name="data-analyst",
        subgraph_name="data_analyst",
    )
