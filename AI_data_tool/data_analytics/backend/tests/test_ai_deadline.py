"""AD-01: one deadline around a whole AI step."""
import asyncio

import pytest

from app.services.ai_deadline import AiStepTimeout, ai_step


async def test_a_step_that_finishes_returns_its_value():
    async def quick():
        return 7
    assert await ai_step(quick(), seconds=1, what="Build the report") == 7


async def test_a_step_past_its_deadline_says_what_did_not_finish():
    async def slow():
        await asyncio.sleep(5)
    with pytest.raises(AiStepTimeout) as err:
        await ai_step(slow(), seconds=0.05, what="Build the report")
    assert "Build the report did not finish in" in str(err.value)


async def test_minutes_are_spelled_as_minutes():
    async def slow():
        await asyncio.sleep(5)
    with pytest.raises(AiStepTimeout) as err:
        await ai_step(slow(), seconds=0.01, what="X")
    assert str(err.value).endswith(" s")
    from app.services.ai_deadline import _span
    assert _span(180) == "3 min"
