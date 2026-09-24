"""Run a step DAG in topological layers under one bounded gate.

Deliberately ~80 lines and owned, not LangGraph (spec S5): every concurrency
path in this codebase is hand-rolled gather + Semaphore, this graph is
acyclic by construction, and the one loop (repair) lives INSIDE a node.

ONE gate for the whole run, not one per layer: the bound is a promise about
load on the customer's database, and a per-layer semaphore would let a wide
layer exceed it.
"""
from __future__ import annotations

import asyncio

from .state import StepResult, StepSpec


def topological_layers(steps: list[StepSpec]) -> list[list[StepSpec]]:
    """Kahn's algorithm, validated: unknown deps and cycles are refused BEFORE
    anything runs — a planner bug must fail the run, never hang it."""
    by_id = {s.id: s for s in steps}
    for s in steps:
        for dep in s.depends_on:
            if dep not in by_id:
                raise ValueError(f"step {s.id!r} depends on unknown step {dep!r}")

    remaining = dict(by_id)
    done: set[str] = set()
    layers: list[list[StepSpec]] = []
    while remaining:
        ready = [s for s in remaining.values()
                 if all(d in done for d in s.depends_on)]
        if not ready:
            raise ValueError(
                f"cycle among steps: {sorted(remaining)}")
        layers.append(ready)
        for s in ready:
            done.add(s.id)
            del remaining[s.id]
    return layers


async def run_dag(steps: list[StepSpec], run_node, gate: asyncio.Semaphore,
                  ) -> dict[str, StepResult]:
    """`run_node(step, parents)` is awaited for each runnable step; `parents`
    maps each dependency id to its StepResult. A failed node fails its
    dependents (skipped_dependency) and never its siblings."""
    layers = topological_layers(steps)
    results: dict[str, StepResult] = {}

    async def one(step: StepSpec) -> StepResult:
        parents = {d: results[d] for d in step.depends_on}
        if any(p.status != "ok" for p in parents.values()):
            blocked = [d for d, p in parents.items() if p.status != "ok"]
            return StepResult(step_id=step.id, status="skipped_dependency",
                              sql=None, rows=None,
                              error=f"dependency failed: {', '.join(blocked)}",
                              validation_failures=[], repair_attempts=0, ms=0)
        async with gate:
            return await run_node(step, parents)

    for layer in layers:
        outcomes = await asyncio.gather(*(one(s) for s in layer),
                                        return_exceptions=True)
        for step, outcome in zip(layer, outcomes):
            if isinstance(outcome, BaseException):
                outcome = StepResult(
                    step_id=step.id, status="failed", sql=None, rows=None,
                    error=f"{type(outcome).__name__}: {outcome}",
                    validation_failures=[], repair_attempts=0, ms=0)
            results[step.id] = outcome
    return results
