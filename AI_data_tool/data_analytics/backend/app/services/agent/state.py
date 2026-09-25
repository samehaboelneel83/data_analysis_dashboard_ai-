"""Typed state passed between the agent's nodes.

Plain dataclasses, not ORM objects: results cross task boundaries and (in the
executor) sometimes thread boundaries, and the catalog-sync work already
established the rule — plain data over the seam, always.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepSpec:
    """One planned step. `depends_on` names other steps whose results this one
    needs — an empty list means it can run in the first layer."""
    id: str
    question: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class StepResult:
    """Every outcome is a value (ok | failed | skipped_dependency), so the
    caller aggregates without interpreting exceptions — the stage_sample
    convention."""
    step_id: str
    status: str
    sql: str | None
    rows: list[dict] | None
    error: str | None
    validation_failures: list[dict]
    repair_attempts: int
    ms: int


def sink_step_ids(steps: list[StepSpec]) -> set[str]:
    """The DAG's sinks: steps no other step `depends_on`. A single-step plan
    is trivially one sink (the step IS the sink). For a multi-step plan,
    intermediate steps exist only to feed a later step's SQL (see graph.py's
    `parent_facts` — their rows are already consumed there); handing their
    raw rows to explain() again invites it to redo that arithmetic itself,
    which is exactly the "confidently wrong ID list over a correct final
    result" failure mode this function exists to close (H6 follow-up)."""
    depended_on = {dep for s in steps for dep in s.depends_on}
    return {s.id for s in steps if s.id not in depended_on}
