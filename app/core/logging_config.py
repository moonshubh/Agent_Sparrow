"""Central structured logging configuration using structlog.

Other modules can do:

    from app.core.logging_config import get_logger
    logger = get_logger(__name__, trace_id="abc123")

All logs are JSON-formatted and include ISO timestamps. The bound *trace_id* helps
correlate log entries across processes and stages of a single analysis run.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Standard library logging setup so that structlog ultimately prints via it.
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(message)s",  # structlog already renders JSON with timestamp, level
    stream=sys.stderr,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# structlog configuration – JSON renderer for production-friendly logs.
# ---------------------------------------------------------------------------
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, LOG_LEVEL, logging.INFO)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(
        file=sys.stderr
    ),  # keep JSON logs off stdout (reserved for JSONRPC)
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(indent=None, sort_keys=True),
    ],
)


def get_logger(name: str, **bound_values: Any) -> structlog.BoundLogger:
    """Return a JSON logger bound with *bound_values* (e.g. trace_id)."""
    return structlog.get_logger(name).bind(**bound_values)
