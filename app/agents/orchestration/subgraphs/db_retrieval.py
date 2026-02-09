"""DB retrieval subgraph builder."""

from __future__ import annotations

from ._base import build_subagent_runner


def build_db_retrieval_subgraph():
    return build_subagent_runner(
        subagent_name="db-retrieval",
        subgraph_name="db_retrieval",
    )
