"""Log analysis subgraph builder."""

from __future__ import annotations

from ._base import SubgraphRunner, build_subagent_runner


def build_log_analysis_subgraph() -> SubgraphRunner:
    return build_subagent_runner(
        subagent_name="log-diagnoser",
        subgraph_name="log_analysis",
    )
