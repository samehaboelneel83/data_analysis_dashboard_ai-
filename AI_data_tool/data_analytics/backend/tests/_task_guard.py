"""Cancel background tasks a test started, before its event loop closes.

A route that detaches work (`asyncio.create_task`) -- a metadata sync, a
metered AI job -- runs it on the app's own session factory, which in tests is
not the in-memory database. Left alone, such a task outlives its test: the
loop closes under it and the garbage collector later destroys it in some other
test, whose run then fails with a GeneratorExit it had nothing to do with.
"""
from __future__ import annotations

import asyncio


async def cancel_tasks_started_since(before: set[asyncio.Task], timeout: float = 5.0) -> int:
    """Cancel every unfinished task that is not in `before` (nor the caller),
    wait for them to end, and return how many were cancelled."""
    me = asyncio.current_task()
    left = [t for t in asyncio.all_tasks() if t not in before and t is not me and not t.done()]
    for t in left:
        t.cancel()
    if left:
        await asyncio.wait(left, timeout=timeout)
    return len(left)
