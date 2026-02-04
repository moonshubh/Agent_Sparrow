"""Utilities for safely running async coroutines from sync contexts.

Avoids event-loop blocking by offloading to a dedicated thread when needed.
"""

from __future__ import annotations

import asyncio
import concurrent.futures as _futures
from typing import Awaitable, TypeVar, Optional

T = TypeVar("T")


def run_coro_blocking(coro: Awaitable[T], timeout: Optional[float] = 30) -> T:
    """Run a coroutine from sync code with a timeout.

    - If no loop is running: use asyncio.run with wait_for.
    - If a loop is running: execute in a dedicated thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout))

    with _futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lambda: asyncio.run(asyncio.wait_for(coro, timeout=timeout)))
        result_timeout = None if timeout is None else timeout + 1
        return fut.result(timeout=result_timeout)
