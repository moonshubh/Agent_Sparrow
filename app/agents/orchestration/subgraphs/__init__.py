"""Registry for orchestration subgraph task runners."""

from __future__ import annotations

from ._base import SubgraphRunner
from .data_analyst import build_data_analyst_subgraph
from .db_retrieval import build_db_retrieval_subgraph
from .draft_writer import build_draft_writer_subgraph
from .log_analysis import build_log_analysis_subgraph
from .research import build_research_subgraph


def build_subgraph_runners() -> dict[str, SubgraphRunner]:
    """Build all supported task subgraph runners."""
    return {
        "research": build_research_subgraph(),
        "log_analysis": build_log_analysis_subgraph(),
        "db_retrieval": build_db_retrieval_subgraph(),
        "draft_writer": build_draft_writer_subgraph(),
        "data_analyst": build_data_analyst_subgraph(),
    }


__all__ = ["build_subgraph_runners", "SubgraphRunner"]
