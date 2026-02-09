"""Draft writer subgraph builder."""

from __future__ import annotations

from ._base import build_subagent_runner


def build_draft_writer_subgraph():
    return build_subagent_runner(
        subagent_name="draft-writer",
        subgraph_name="draft_writer",
    )
