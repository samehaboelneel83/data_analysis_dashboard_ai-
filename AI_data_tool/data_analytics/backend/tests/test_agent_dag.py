"""The executor: topological layers, one bounded gate, failures contained.

Mirrors stage_sample's proven shape (gather + semaphore + every outcome a
value). What is new is dependency handling: a failed node fails its
DEPENDENTS and never its SIBLINGS — the property the whole plan/execute
split rests on.
"""
import asyncio

import pytest

from app.services.agent.dag import run_dag
from app.services.agent.state import StepResult, StepSpec


def ok(step, parents):
    return StepResult(step_id=step.id, status="ok", sql=None, rows=[{"n": 1}],
                      error=None, validation_failures=[], repair_attempts=0, ms=1)


class TestTopology:
    async def test_independent_steps_overlap(self):
        live, peak = [], [0]

        async def slow(step, parents):
            live.append(step.id); peak[0] = max(peak[0], len(live))
            await asyncio.sleep(0.05)
            live.remove(step.id)
            return ok(step, parents)

        steps = [StepSpec(id=f"s{i}", question="q", depends_on=[]) for i in range(4)]
        await run_dag(steps, slow, asyncio.Semaphore(4))
        assert peak[0] > 1, "independent steps ran one at a time"

    async def test_the_gate_bounds_width(self):
        live, peak = [], [0]

        async def slow(step, parents):
            live.append(step.id); peak[0] = max(peak[0], len(live))
            await asyncio.sleep(0.05)
            live.remove(step.id)
            return ok(step, parents)

        steps = [StepSpec(id=f"s{i}", question="q", depends_on=[]) for i in range(8)]
        await run_dag(steps, slow, asyncio.Semaphore(2))
        assert peak[0] <= 2

    async def test_a_dependent_sees_its_parents_result(self):
        seen = {}

        async def node(step, parents):
            seen[step.id] = {k: v.rows for k, v in parents.items()}
            return ok(step, parents)

        await run_dag([StepSpec("a", "q", []), StepSpec("b", "q", ["a"])],
                      node, asyncio.Semaphore(4))
        assert seen["b"] == {"a": [{"n": 1}]}

    async def test_a_parent_completes_before_its_child_starts(self):
        order = []

        async def node(step, parents):
            order.append(("start", step.id))
            await asyncio.sleep(0.02)
            order.append(("end", step.id))
            return ok(step, parents)

        await run_dag([StepSpec("a", "q", []), StepSpec("b", "q", ["a"])],
                      node, asyncio.Semaphore(4))
        assert order.index(("end", "a")) < order.index(("start", "b"))


class TestFailureContainment:
    async def test_a_failed_node_fails_dependents_not_siblings(self):
        async def node(step, parents):
            if step.id == "bad":
                raise RuntimeError("boom")
            return ok(step, parents)

        results = await run_dag(
            [StepSpec("bad", "q", []), StepSpec("sibling", "q", []),
             StepSpec("child_of_bad", "q", ["bad"])],
            node, asyncio.Semaphore(4))

        assert results["sibling"].status == "ok"
        assert results["bad"].status == "failed"
        assert results["child_of_bad"].status == "skipped_dependency"

    async def test_a_node_returning_failed_also_skips_dependents(self):
        async def node(step, parents):
            if step.id == "a":
                return StepResult(step_id="a", status="failed", sql=None,
                                  rows=None, error="ladder rejected",
                                  validation_failures=[], repair_attempts=3, ms=1)
            return ok(step, parents)

        results = await run_dag([StepSpec("a", "q", []), StepSpec("b", "q", ["a"])],
                                node, asyncio.Semaphore(4))
        assert results["b"].status == "skipped_dependency"


class TestBadGraphsAreRefusedUpFront:
    async def test_a_cycle_is_an_error_before_anything_runs(self):
        ran = []

        async def node(step, parents):
            ran.append(step.id)
            return ok(step, parents)

        with pytest.raises(ValueError, match="cycle"):
            await run_dag([StepSpec("a", "q", ["b"]), StepSpec("b", "q", ["a"])],
                          node, asyncio.Semaphore(4))
        assert ran == []

    async def test_an_unknown_dependency_is_an_error(self):
        with pytest.raises(ValueError, match="unknown"):
            await run_dag([StepSpec("a", "q", ["ghost"])],
                          lambda s, p: None, asyncio.Semaphore(4))
