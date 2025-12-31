from __future__ import annotations

import logging
import os
import sys

from loguru import logger


def configure_logging(*, production: bool) -> str:
    """Configure log levels for both stdlib `logging` and Loguru.

    Defaults to INFO in production, DEBUG otherwise. Override via `LOG_LEVEL`.
    """

    level_name = (os.getenv("LOG_LEVEL") or ("INFO" if production else "DEBUG")).upper()
    level_value = logging._nameToLevel.get(level_name, logging.INFO)

    # Standard library logging (FastAPI/Uvicorn/etc.)
    logging.getLogger().setLevel(level_value)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).setLevel(level_value)

    # Loguru (used across agent code)
    logger.remove()
    logger.add(
        sys.stdout,
        level=level_name,
        backtrace=False,
        diagnose=False,
    )

    return level_name

