"""A time limit for a whole AI step (AD-01).

`LLMClient` bounds each HTTP call, but a step may make several calls, retry,
and do database work in between; nothing bounded the WHOLE step, so a step
could "run" for many minutes. `ai_step` puts one deadline around it and turns
running out of time into an error that says, in words, what did not finish.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


class AiStepTimeout(Exception):
    """A step ran past its deadline; the message is fit to show a person."""


def _span(seconds: float) -> str:
    if seconds >= 60:
        m = round(seconds / 60)
        return f"{m} min"
    return f"{max(1, round(seconds))} s"


async def ai_step(coro: Awaitable[T], *, seconds: float, what: str) -> T:
    """Await `coro`, or raise `AiStepTimeout("<what> did not finish in N min")`
    after `seconds`. The awaited work is cancelled on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError as exc:
        raise AiStepTimeout(f"{what} did not finish in {_span(seconds)}") from exc
