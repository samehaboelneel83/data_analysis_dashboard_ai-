"""Question -> typed step DAG.

'Decomposition into ordered steps' (ARCHITECTURE.md plan.py) generalised: a
dependency DAG whose degenerate case is one step — and one step is also the
FALLBACK, because a planner failure must degrade to 'answer it as a single
query', never kill the run.
"""
from __future__ import annotations

from .context import SchemaContext
from .dag import topological_layers
from .state import StepSpec

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array", "minItems": 1, "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "question": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "question", "depends_on"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["steps"],
    "additionalProperties": False,
}


async def plan_steps(question: str, intent: str, context: SchemaContext,
                     client) -> list[StepSpec]:
    fallback = [StepSpec(id="s1", question=question, depends_on=[])]

    got = await client.complete_json(
        [{"role": "system", "content": (
            "Decompose a business question into 1-6 SQL-answerable steps. "
            "Most questions are ONE step; only decompose when sub-answers "
            "genuinely feed each other (a compare of two computed figures, "
            "a filter derived from another query). `depends_on` lists step "
            "ids whose results a step needs. "
            "A ranking/top-N question paired with its measure (\"which X "
            "... and how many/much ...\") is ONE SQL query — GROUP BY the "
            "entity, aggregate the measure, ORDER BY it, LIMIT N — never a "
            "compute step followed by a lookup/format step; the single "
            "query already returns both the winners and their counts. "
            "Decompose only when a later step needs a DIFFERENT table's "
            "data that cannot be reached via the allowed joins, or is a "
            "genuinely separate computation.")},
         {"role": "user", "content": (
             f"Database:\n{context.render(max_chars=3000)}\n\n"
             f"Intent: {intent}\nQuestion: {question}")}],
        PLAN_SCHEMA, enforce=True, max_tokens=400, temperature=0.0)
    if not got:
        return fallback

    steps = [StepSpec(id=s["id"], question=s["question"],
                      depends_on=list(s["depends_on"])) for s in got["steps"]]
    try:
        topological_layers(steps)  # validates ids and acyclicity
    except ValueError:
        return fallback
    return steps
